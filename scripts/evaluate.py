#!/usr/bin/env python3
"""
MetadataHub Evaluation Framework

Evaluates retrieval quality using ground truth queries.
Calculates Recall@K, MRR, and Tree Accuracy metrics.
"""

import argparse
import json
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.config import Config


@dataclass
class EvalResult:
    """Result of evaluating a single query."""
    query_id: str
    query: str
    category: str
    
    # Search results
    retrieved_sources: list[str] = field(default_factory=list)
    expected_sources: list[str] = field(default_factory=list)
    
    # Tree results
    retrieved_nodes: list[str] = field(default_factory=list)
    expected_nodes: list[str] = field(default_factory=list)
    
    # Scores
    recall_at_k: dict[int, float] = field(default_factory=dict)
    reciprocal_rank: float = 0.0
    tree_accuracy: float = 0.0
    
    # Metadata
    search_time_ms: float = 0.0
    error: Optional[str] = None


@dataclass
class EvalSummary:
    """Summary of evaluation run."""
    store_path: str
    timestamp: str
    num_queries: int
    language: str
    k_values: list[int]
    
    # Aggregate metrics
    avg_recall_at_k: dict[int, float] = field(default_factory=dict)
    avg_mrr: float = 0.0
    avg_tree_accuracy: float = 0.0
    
    # By category
    by_category: dict[str, dict] = field(default_factory=dict)
    
    # Individual results
    results: list[dict] = field(default_factory=list)


def calc_recall_at_k(retrieved: list[str], expected: list[str], k: int) -> float:
    """
    Calculate Recall@K.
    
    Args:
        retrieved: List of retrieved document IDs/names (ordered by rank)
        expected: List of relevant document IDs/names
        k: Number of top results to consider
    
    Returns:
        Recall score (0.0 to 1.0)
    """
    if not expected:
        return 1.0  # No expected = trivially satisfied
    
    top_k = set(retrieved[:k])
    expected_set = set(expected)
    
    hits = len(top_k & expected_set)
    return hits / len(expected_set)


def calc_mrr(retrieved: list[str], expected: list[str]) -> float:
    """
    Calculate Mean Reciprocal Rank for a single query.
    
    Args:
        retrieved: List of retrieved document IDs/names (ordered by rank)
        expected: List of relevant document IDs/names
    
    Returns:
        Reciprocal rank (1/position of first relevant, or 0 if none found)
    """
    if not expected:
        return 1.0  # No expected = trivially satisfied
    
    expected_set = set(expected)
    
    for i, doc in enumerate(retrieved, start=1):
        if doc in expected_set:
            return 1.0 / i
    
    return 0.0


def calc_tree_accuracy(retrieved_nodes: list[str], expected_nodes: list[str]) -> float:
    """
    Calculate tree navigation accuracy.
    
    Args:
        retrieved_nodes: List of nodes reached via tree navigation
        expected_nodes: List of nodes that should contain the answer
    
    Returns:
        Accuracy score (0.0 to 1.0)
    """
    if not expected_nodes:
        return 1.0  # No expected = trivially satisfied
    
    if not retrieved_nodes:
        return 0.0
    
    retrieved_set = set(retrieved_nodes)
    expected_set = set(expected_nodes)
    
    hits = len(retrieved_set & expected_set)
    return hits / len(expected_set)


def evaluate_query(
    query_data: dict,
    store_path: str,
    language: str = "en",
    k_values: list[int] = None,
    verbose: bool = False
) -> EvalResult:
    """
    Evaluate a single query against ground truth.
    
    Args:
        query_data: Query dict from ground_truth.json
        store_path: Path to MetadataHub store
        language: "en" or "vi" for query language
        k_values: List of K values for Recall@K
        verbose: Print debug info
    
    Returns:
        EvalResult with all metrics
    """
    import time
    
    if k_values is None:
        k_values = [1, 3, 5, 10]
    
    # Select query based on language
    query_text = query_data.get(f"query_{language}", query_data.get("query", ""))
    if not query_text:
        query_text = query_data.get("query", "")
    
    result = EvalResult(
        query_id=query_data["id"],
        query=query_text,
        category=query_data.get("category", "unknown"),
        expected_sources=query_data.get("expected_sources", []),
        expected_nodes=query_data.get("expected_nodes", [])
    )
    
    try:
        # Import search function
        from skills.metadatahub.search import search
        
        # Run search
        start_time = time.time()
        search_results = search(query_text, store_path=store_path, top_k=max(k_values))
        result.search_time_ms = (time.time() - start_time) * 1000
        
        # Extract retrieved source names
        result.retrieved_sources = [
            r.get("filename", r.get("source_id", "unknown"))
            for r in search_results
        ]
        
        if verbose:
            print(f"  Query: {query_text}")
            print(f"  Retrieved: {result.retrieved_sources[:5]}")
            print(f"  Expected: {result.expected_sources}")
        
        # Calculate Recall@K for each K
        for k in k_values:
            result.recall_at_k[k] = calc_recall_at_k(
                result.retrieved_sources,
                result.expected_sources,
                k
            )
        
        # Calculate MRR
        result.reciprocal_rank = calc_mrr(
            result.retrieved_sources,
            result.expected_sources
        )
        
        # Tree accuracy (if we have search results)
        if search_results and result.expected_nodes:
            try:
                from skills.metadatahub.deep_retrieve import retrieve
                
                # Get first relevant source
                first_source = search_results[0]
                source_id = first_source.get("source_id", first_source.get("id"))
                
                if source_id:
                    tree_data = retrieve(source_id, store_path=store_path)
                    
                    # Extract node IDs from tree
                    def extract_node_ids(node, ids=None):
                        if ids is None:
                            ids = []
                        if isinstance(node, dict):
                            if "id" in node:
                                ids.append(node["id"])
                            for child in node.get("children", []):
                                extract_node_ids(child, ids)
                        return ids
                    
                    result.retrieved_nodes = extract_node_ids(tree_data)
                    result.tree_accuracy = calc_tree_accuracy(
                        result.retrieved_nodes,
                        result.expected_nodes
                    )
            except Exception as e:
                if verbose:
                    print(f"  Tree retrieval error: {e}")
                result.tree_accuracy = 0.0
        
    except ImportError as e:
        result.error = f"Import error: {e}. Make sure MetadataHub is properly installed."
    except Exception as e:
        result.error = str(e)
        if verbose:
            print(f"  Error: {e}")
    
    return result


def run_evaluation(
    ground_truth_path: str,
    store_path: str,
    language: str = "en",
    category: Optional[str] = None,
    k_values: list[int] = None,
    verbose: bool = False
) -> EvalSummary:
    """
    Run full evaluation pipeline.
    
    Args:
        ground_truth_path: Path to ground_truth.json
        store_path: Path to MetadataHub store
        language: "en" or "vi"
        category: Filter by category (None = all)
        k_values: List of K values for Recall@K
        verbose: Print progress
    
    Returns:
        EvalSummary with aggregate and per-query results
    """
    if k_values is None:
        k_values = [1, 3, 5, 10]
    
    # Load ground truth
    with open(ground_truth_path) as f:
        ground_truth = json.load(f)
    
    queries = ground_truth.get("queries", [])
    
    # Filter by category if specified
    if category:
        queries = [q for q in queries if q.get("category") == category]
    
    if verbose:
        print(f"Evaluating {len(queries)} queries...")
    
    # Run evaluation for each query
    results = []
    for i, query_data in enumerate(queries):
        if verbose:
            print(f"\n[{i+1}/{len(queries)}] {query_data['id']}")
        
        result = evaluate_query(
            query_data,
            store_path,
            language=language,
            k_values=k_values,
            verbose=verbose
        )
        results.append(result)
    
    # Aggregate metrics
    summary = EvalSummary(
        store_path=store_path,
        timestamp=datetime.now().isoformat(),
        num_queries=len(results),
        language=language,
        k_values=k_values
    )
    
    # Calculate averages
    if results:
        for k in k_values:
            recalls = [r.recall_at_k.get(k, 0) for r in results if r.error is None]
            summary.avg_recall_at_k[k] = sum(recalls) / len(recalls) if recalls else 0
        
        mrrs = [r.reciprocal_rank for r in results if r.error is None]
        summary.avg_mrr = sum(mrrs) / len(mrrs) if mrrs else 0
        
        tree_accs = [r.tree_accuracy for r in results if r.error is None]
        summary.avg_tree_accuracy = sum(tree_accs) / len(tree_accs) if tree_accs else 0
    
    # By category
    categories = set(r.category for r in results)
    for cat in categories:
        cat_results = [r for r in results if r.category == cat and r.error is None]
        if cat_results:
            summary.by_category[cat] = {
                "num_queries": len(cat_results),
                "avg_recall_at_k": {
                    k: sum(r.recall_at_k.get(k, 0) for r in cat_results) / len(cat_results)
                    for k in k_values
                },
                "avg_mrr": sum(r.reciprocal_rank for r in cat_results) / len(cat_results),
                "avg_tree_accuracy": sum(r.tree_accuracy for r in cat_results) / len(cat_results)
            }
    
    # Store individual results
    summary.results = [asdict(r) for r in results]
    
    return summary


def print_summary(summary: EvalSummary):
    """Print formatted evaluation summary."""
    print("\n" + "=" * 50)
    print("MetadataHub Evaluation Results")
    print("=" * 50)
    print(f"Store: {summary.store_path}")
    print(f"Queries: {summary.num_queries}")
    print(f"Language: {summary.language}")
    print(f"Timestamp: {summary.timestamp}")
    
    print("\nResults:")
    for k in summary.k_values:
        recall = summary.avg_recall_at_k.get(k, 0)
        queries_with_hits = sum(
            1 for r in summary.results 
            if r.get("recall_at_k", {}).get(str(k), r.get("recall_at_k", {}).get(k, 0)) > 0
        )
        print(f"  Recall@{k}: {recall:.2f} ({queries_with_hits}/{summary.num_queries} queries with relevant in top {k})")
    
    print(f"  MRR: {summary.avg_mrr:.2f}")
    print(f"  Tree Accuracy: {summary.avg_tree_accuracy:.2f}")
    
    if summary.by_category:
        print("\nBy Category:")
        for cat, metrics in summary.by_category.items():
            recall_3 = metrics["avg_recall_at_k"].get(3, metrics["avg_recall_at_k"].get("3", 0))
            mrr = metrics["avg_mrr"]
            print(f"  {cat:15} Recall@3={recall_3:.2f}, MRR={mrr:.2f}")
    
    # Show errors if any
    errors = [r for r in summary.results if r.get("error")]
    if errors:
        print(f"\nErrors: {len(errors)} queries failed")
        for r in errors[:3]:
            print(f"  - {r['query_id']}: {r['error'][:50]}...")


def main():
    parser = argparse.ArgumentParser(
        description="Evaluate MetadataHub retrieval quality"
    )
    parser.add_argument(
        "--store", "-s",
        required=True,
        help="Path to MetadataHub store"
    )
    parser.add_argument(
        "--ground-truth", "-g",
        default="evaluation/ground_truth.json",
        help="Path to ground truth file (default: evaluation/ground_truth.json)"
    )
    parser.add_argument(
        "--output", "-o",
        help="Save results to JSON file"
    )
    parser.add_argument(
        "--language", "-l",
        choices=["en", "vi"],
        default="en",
        help="Query language (default: en)"
    )
    parser.add_argument(
        "--category", "-c",
        choices=["financial", "code", "documentation"],
        help="Filter by category"
    )
    parser.add_argument(
        "--k",
        type=int,
        nargs="+",
        default=[1, 3, 5, 10],
        help="K values for Recall@K (default: 1 3 5 10)"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Print detailed progress"
    )
    
    args = parser.parse_args()
    
    # Resolve paths
    ground_truth_path = Path(args.ground_truth)
    if not ground_truth_path.is_absolute():
        # Try relative to script location
        script_dir = Path(__file__).parent.parent
        ground_truth_path = script_dir / args.ground_truth
    
    if not ground_truth_path.exists():
        print(f"Error: Ground truth file not found: {ground_truth_path}")
        sys.exit(1)
    
    # Run evaluation
    summary = run_evaluation(
        str(ground_truth_path),
        args.store,
        language=args.language,
        category=args.category,
        k_values=args.k,
        verbose=args.verbose
    )
    
    # Print results
    print_summary(summary)
    
    # Save to file if requested
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(asdict(summary), f, indent=2)
        print(f"\nResults saved to: {output_path}")


if __name__ == "__main__":
    main()
