#!/usr/bin/env python3
"""
RAG System Benchmark Runner

Compares MetadataHub vs LlamaIndex vs LangChain+FAISS on the same corpus and queries.

Usage:
    python run_benchmark.py                          # Run all systems
    python run_benchmark.py --systems metadatahub    # Run specific system
    python run_benchmark.py --output results.json    # Save to file
    python run_benchmark.py --top-k 5 10            # Test multiple K values
"""

import argparse
import json
import sys
import time
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from systems import MetadataHubRunner, LlamaIndexRunner, LangChainRunner, BaseRunner


@dataclass
class QueryResult:
    """Result of a single query evaluation."""
    query_id: str
    query: str
    category: str
    expected_sources: list[str]
    retrieved_sources: list[str]
    scores: list[float]
    latency_ms: float
    hit_at_1: bool
    hit_at_3: bool
    hit_at_5: bool
    hit_at_10: bool
    reciprocal_rank: float
    
    
@dataclass
class SystemBenchmark:
    """Benchmark results for a single system."""
    system_name: str
    index_time_seconds: float
    index_size_mb: float
    num_documents: int
    num_chunks: int
    
    # Aggregated metrics
    recall_at_1: float = 0.0
    recall_at_3: float = 0.0
    recall_at_5: float = 0.0
    recall_at_10: float = 0.0
    mrr: float = 0.0  # Mean Reciprocal Rank
    avg_latency_ms: float = 0.0
    p50_latency_ms: float = 0.0
    p95_latency_ms: float = 0.0
    
    # By category
    metrics_by_category: dict = field(default_factory=dict)
    
    # Individual query results
    query_results: list[QueryResult] = field(default_factory=list)
    
    
@dataclass
class BenchmarkReport:
    """Complete benchmark report."""
    timestamp: str
    corpus_path: str
    num_queries: int
    systems: list[SystemBenchmark]
    comparison_table: str = ""


def load_ground_truth(path: Path) -> dict:
    """Load ground truth queries."""
    with open(path) as f:
        return json.load(f)


def evaluate_query(
    runner: BaseRunner,
    query_data: dict,
    top_k: int = 10,
    use_vietnamese: bool = False
) -> QueryResult:
    """
    Evaluate a single query against the ground truth.
    
    Args:
        runner: The RAG system runner
        query_data: Query from ground truth
        top_k: Number of results to retrieve
        use_vietnamese: Use Vietnamese query variant
        
    Returns:
        QueryResult with metrics
    """
    query = query_data.get("query_vi" if use_vietnamese else "query", "")
    expected_sources = query_data.get("expected_sources", [])
    
    # Run search with timing
    results, latency_ms = runner.timed_search(query, top_k)
    
    # Extract retrieved sources
    retrieved_sources = [r.source for r in results]
    scores = [r.score for r in results]
    
    # Calculate hits at various K
    def has_hit_at_k(k: int) -> bool:
        for source in retrieved_sources[:k]:
            for expected in expected_sources:
                if expected.lower() in source.lower() or source.lower() in expected.lower():
                    return True
        return False
    
    # Calculate reciprocal rank
    rr = 0.0
    for i, source in enumerate(retrieved_sources):
        for expected in expected_sources:
            if expected.lower() in source.lower() or source.lower() in expected.lower():
                rr = 1.0 / (i + 1)
                break
        if rr > 0:
            break
    
    return QueryResult(
        query_id=query_data.get("id", "unknown"),
        query=query,
        category=query_data.get("category", "unknown"),
        expected_sources=expected_sources,
        retrieved_sources=retrieved_sources[:top_k],
        scores=scores[:top_k],
        latency_ms=latency_ms,
        hit_at_1=has_hit_at_k(1),
        hit_at_3=has_hit_at_k(3),
        hit_at_5=has_hit_at_k(5),
        hit_at_10=has_hit_at_k(10),
        reciprocal_rank=rr
    )


def run_system_benchmark(
    runner: BaseRunner,
    corpus_path: Path,
    ground_truth: dict,
    top_k: int = 10,
    use_vietnamese: bool = False
) -> SystemBenchmark:
    """
    Run complete benchmark for a single system.
    
    Args:
        runner: RAG system runner
        corpus_path: Path to corpus
        ground_truth: Ground truth data
        top_k: Max results to retrieve
        use_vietnamese: Use Vietnamese queries
        
    Returns:
        SystemBenchmark with all metrics
    """
    print(f"\n{'='*60}")
    print(f"Benchmarking: {runner.name}")
    print(f"{'='*60}")
    
    # Index corpus
    print(f"\n📚 Indexing corpus...")
    try:
        stats = runner.index(str(corpus_path))
        print(f"   ✓ Indexed {stats.num_documents} documents ({stats.num_chunks} chunks)")
        print(f"   ✓ Index size: {stats.index_size_mb:.2f} MB")
        print(f"   ✓ Index time: {stats.index_time_seconds:.2f}s")
    except Exception as e:
        print(f"   ✗ Indexing failed: {e}")
        return SystemBenchmark(
            system_name=runner.name,
            index_time_seconds=0,
            index_size_mb=0,
            num_documents=0,
            num_chunks=0
        )
    
    # Run queries
    queries = ground_truth.get("queries", [])
    print(f"\n🔍 Running {len(queries)} queries...")
    
    query_results = []
    latencies = []
    
    for i, q in enumerate(queries):
        result = evaluate_query(runner, q, top_k, use_vietnamese)
        query_results.append(result)
        latencies.append(result.latency_ms)
        
        # Progress indicator
        if (i + 1) % 10 == 0:
            print(f"   Processed {i + 1}/{len(queries)} queries...")
    
    # Calculate aggregated metrics
    n = len(query_results)
    recall_at_1 = sum(1 for r in query_results if r.hit_at_1) / n if n > 0 else 0
    recall_at_3 = sum(1 for r in query_results if r.hit_at_3) / n if n > 0 else 0
    recall_at_5 = sum(1 for r in query_results if r.hit_at_5) / n if n > 0 else 0
    recall_at_10 = sum(1 for r in query_results if r.hit_at_10) / n if n > 0 else 0
    mrr = sum(r.reciprocal_rank for r in query_results) / n if n > 0 else 0
    
    # Latency stats
    sorted_latencies = sorted(latencies)
    avg_latency = sum(latencies) / len(latencies) if latencies else 0
    p50_latency = sorted_latencies[len(sorted_latencies) // 2] if sorted_latencies else 0
    p95_idx = int(len(sorted_latencies) * 0.95)
    p95_latency = sorted_latencies[p95_idx] if sorted_latencies else 0
    
    # Metrics by category
    metrics_by_category = {}
    for category in set(r.category for r in query_results):
        cat_results = [r for r in query_results if r.category == category]
        cat_n = len(cat_results)
        metrics_by_category[category] = {
            "count": cat_n,
            "recall_at_3": sum(1 for r in cat_results if r.hit_at_3) / cat_n if cat_n > 0 else 0,
            "recall_at_5": sum(1 for r in cat_results if r.hit_at_5) / cat_n if cat_n > 0 else 0,
            "mrr": sum(r.reciprocal_rank for r in cat_results) / cat_n if cat_n > 0 else 0,
        }
    
    benchmark = SystemBenchmark(
        system_name=runner.name,
        index_time_seconds=stats.index_time_seconds,
        index_size_mb=stats.index_size_mb,
        num_documents=stats.num_documents,
        num_chunks=stats.num_chunks,
        recall_at_1=recall_at_1,
        recall_at_3=recall_at_3,
        recall_at_5=recall_at_5,
        recall_at_10=recall_at_10,
        mrr=mrr,
        avg_latency_ms=avg_latency,
        p50_latency_ms=p50_latency,
        p95_latency_ms=p95_latency,
        metrics_by_category=metrics_by_category,
        query_results=query_results
    )
    
    # Print summary
    print(f"\n📊 Results for {runner.name}:")
    print(f"   Recall@1:  {recall_at_1:.1%}")
    print(f"   Recall@3:  {recall_at_3:.1%}")
    print(f"   Recall@5:  {recall_at_5:.1%}")
    print(f"   Recall@10: {recall_at_10:.1%}")
    print(f"   MRR:       {mrr:.3f}")
    print(f"   Latency:   {avg_latency:.1f}ms avg, {p50_latency:.1f}ms p50, {p95_latency:.1f}ms p95")
    
    # Cleanup
    runner.cleanup()
    
    return benchmark


def generate_comparison_table(systems: list[SystemBenchmark]) -> str:
    """Generate a markdown comparison table."""
    if not systems:
        return ""
    
    # Header
    lines = [
        "## Benchmark Results Comparison",
        "",
        "| Metric | " + " | ".join(s.system_name for s in systems) + " |",
        "|--------|" + "|".join("-" * 12 for _ in systems) + "|",
    ]
    
    # Metrics rows
    metrics = [
        ("Recall@1", "recall_at_1", lambda x: f"{x:.1%}"),
        ("Recall@3", "recall_at_3", lambda x: f"{x:.1%}"),
        ("Recall@5", "recall_at_5", lambda x: f"{x:.1%}"),
        ("Recall@10", "recall_at_10", lambda x: f"{x:.1%}"),
        ("MRR", "mrr", lambda x: f"{x:.3f}"),
        ("Avg Latency (ms)", "avg_latency_ms", lambda x: f"{x:.1f}"),
        ("P95 Latency (ms)", "p95_latency_ms", lambda x: f"{x:.1f}"),
        ("Index Size (MB)", "index_size_mb", lambda x: f"{x:.2f}"),
        ("Index Time (s)", "index_time_seconds", lambda x: f"{x:.2f}"),
        ("Chunks", "num_chunks", lambda x: f"{x:,}"),
    ]
    
    for label, attr, fmt in metrics:
        values = [fmt(getattr(s, attr)) for s in systems]
        lines.append(f"| {label} | " + " | ".join(values) + " |")
    
    # By category breakdown
    lines.extend([
        "",
        "### By Category",
        ""
    ])
    
    categories = set()
    for s in systems:
        categories.update(s.metrics_by_category.keys())
    
    for category in sorted(categories):
        lines.append(f"\n**{category.title()}**")
        lines.append("")
        lines.append("| Metric | " + " | ".join(s.system_name for s in systems) + " |")
        lines.append("|--------|" + "|".join("-" * 12 for _ in systems) + "|")
        
        for metric, key in [("Recall@3", "recall_at_3"), ("Recall@5", "recall_at_5"), ("MRR", "mrr")]:
            values = []
            for s in systems:
                cat_metrics = s.metrics_by_category.get(category, {})
                val = cat_metrics.get(key, 0)
                values.append(f"{val:.1%}" if "recall" in key else f"{val:.3f}")
            lines.append(f"| {metric} | " + " | ".join(values) + " |")
    
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Benchmark RAG systems",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--corpus",
        type=Path,
        default=Path(__file__).parent / "corpus",
        help="Path to corpus directory"
    )
    parser.add_argument(
        "--ground-truth",
        type=Path,
        default=Path(__file__).parent / "ground_truth.json",
        help="Path to ground truth JSON"
    )
    parser.add_argument(
        "--systems",
        nargs="+",
        choices=["metadatahub", "llamaindex", "langchain", "all"],
        default=["all"],
        help="Systems to benchmark"
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Output JSON file for results"
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=10,
        help="Number of results to retrieve (default: 10)"
    )
    parser.add_argument(
        "--vietnamese",
        action="store_true",
        help="Use Vietnamese queries"
    )
    
    args = parser.parse_args()
    
    # Validate inputs
    if not args.corpus.exists():
        print(f"Error: Corpus not found at {args.corpus}")
        sys.exit(1)
    
    if not args.ground_truth.exists():
        print(f"Error: Ground truth not found at {args.ground_truth}")
        sys.exit(1)
    
    # Load ground truth
    print(f"📄 Loading ground truth from {args.ground_truth}")
    ground_truth = load_ground_truth(args.ground_truth)
    num_queries = len(ground_truth.get("queries", []))
    print(f"   Found {num_queries} queries")
    
    # Determine which systems to run
    systems_to_run = args.systems
    if "all" in systems_to_run:
        systems_to_run = ["metadatahub", "llamaindex", "langchain"]
    
    # Create runners
    runners = []
    for system in systems_to_run:
        if system == "metadatahub":
            runners.append(MetadataHubRunner())
        elif system == "llamaindex":
            runners.append(LlamaIndexRunner())
        elif system == "langchain":
            runners.append(LangChainRunner())
    
    # Run benchmarks
    print(f"\n🚀 Starting benchmark with {len(runners)} systems")
    print(f"   Corpus: {args.corpus}")
    print(f"   Top-K: {args.top_k}")
    print(f"   Language: {'Vietnamese' if args.vietnamese else 'English'}")
    
    system_benchmarks = []
    for runner in runners:
        try:
            benchmark = run_system_benchmark(
                runner,
                args.corpus,
                ground_truth,
                args.top_k,
                args.vietnamese
            )
            system_benchmarks.append(benchmark)
        except Exception as e:
            print(f"\n❌ Error benchmarking {runner.name}: {e}")
            import traceback
            traceback.print_exc()
    
    # Generate comparison
    comparison_table = generate_comparison_table(system_benchmarks)
    
    # Create report
    report = BenchmarkReport(
        timestamp=datetime.now().isoformat(),
        corpus_path=str(args.corpus),
        num_queries=num_queries,
        systems=system_benchmarks,
        comparison_table=comparison_table
    )
    
    # Print comparison table
    print(f"\n{'='*60}")
    print("COMPARISON SUMMARY")
    print(f"{'='*60}")
    print(comparison_table)
    
    # Save results
    if args.output:
        # Convert to JSON-serializable format
        output_data = {
            "timestamp": report.timestamp,
            "corpus_path": report.corpus_path,
            "num_queries": report.num_queries,
            "comparison_table": report.comparison_table,
            "systems": []
        }
        
        for s in report.systems:
            system_data = {
                "system_name": s.system_name,
                "index_time_seconds": s.index_time_seconds,
                "index_size_mb": s.index_size_mb,
                "num_documents": s.num_documents,
                "num_chunks": s.num_chunks,
                "recall_at_1": s.recall_at_1,
                "recall_at_3": s.recall_at_3,
                "recall_at_5": s.recall_at_5,
                "recall_at_10": s.recall_at_10,
                "mrr": s.mrr,
                "avg_latency_ms": s.avg_latency_ms,
                "p50_latency_ms": s.p50_latency_ms,
                "p95_latency_ms": s.p95_latency_ms,
                "metrics_by_category": s.metrics_by_category,
                "query_results": [
                    {
                        "query_id": r.query_id,
                        "query": r.query,
                        "category": r.category,
                        "expected_sources": r.expected_sources,
                        "retrieved_sources": r.retrieved_sources,
                        "hit_at_1": r.hit_at_1,
                        "hit_at_3": r.hit_at_3,
                        "hit_at_5": r.hit_at_5,
                        "reciprocal_rank": r.reciprocal_rank,
                        "latency_ms": r.latency_ms
                    }
                    for r in s.query_results
                ]
            }
            output_data["systems"].append(system_data)
        
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with open(args.output, "w") as f:
            json.dump(output_data, f, indent=2)
        print(f"\n💾 Results saved to {args.output}")
    
    # Also save markdown report
    if args.output:
        md_path = args.output.with_suffix(".md")
        with open(md_path, "w") as f:
            f.write(f"# RAG Benchmark Report\n\n")
            f.write(f"**Date:** {report.timestamp}\n\n")
            f.write(f"**Corpus:** {report.corpus_path}\n\n")
            f.write(f"**Queries:** {report.num_queries}\n\n")
            f.write(comparison_table)
        print(f"📝 Markdown report saved to {md_path}")
    
    print("\n✅ Benchmark complete!")
    
    return report


if __name__ == "__main__":
    main()
