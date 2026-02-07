#!/usr/bin/env python3
"""
MetadataHub Drill-Down Benchmark (Simplified)

Tests Tier 1 (source retrieval) and Tier 2 (hint quality for navigation).

Key insight: Instead of exact path matching, we verify that:
1. The correct source file is retrieved
2. The hint contains enough information to guide navigation
   (sheet name, relevant column/row labels)

Usage:
    python run_drilldown_benchmark.py                    # Full run
    python run_drilldown_benchmark.py --skip-ingest      # Skip indexing (use existing)
    python run_drilldown_benchmark.py --verbose          # Show detailed output
"""

import argparse
import json
import sys
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.config import Config, init_config
from scripts.catalog import load_catalog
from scripts.build_vectors import search
from scripts.build_tree import load_tree


@dataclass
class Tier1Result:
    """Result of Tier 1 (source retrieval)."""
    query: str
    expected_source: str
    retrieved_sources: list[str]
    scores: list[float]
    hit: bool
    rank: int  # 0 if not found
    latency_ms: float


@dataclass
class HintResult:
    """Result of hint quality check (Tier 2 simplified)."""
    expected_path: list[str]
    hint: Optional[str]
    hint_contains_sheet: bool
    hint_contains_context: bool  # Has relevant row/column info
    content_preview: Optional[str]
    content_has_value: bool  # Expected value found in preview/content
    latency_ms: float


@dataclass
class QueryResult:
    """Combined result for a query."""
    id: str
    query: str
    category: str
    tier1: Tier1Result
    hint_result: Optional[HintResult]
    success: bool  # Overall success


@dataclass
class BenchmarkResults:
    """Aggregate benchmark results."""
    timestamp: str
    corpus_path: str
    num_queries: int
    index_time_seconds: float
    
    # Tier 1 metrics
    tier1_recall_at_1: float = 0.0
    tier1_recall_at_3: float = 0.0
    tier1_recall_at_5: float = 0.0
    tier1_mrr: float = 0.0
    tier1_avg_latency_ms: float = 0.0
    
    # Hint quality metrics (Tier 2 simplified)
    hint_sheet_accuracy: float = 0.0  # % where hint includes correct sheet
    hint_context_rate: float = 0.0    # % with useful row/col context
    content_match_rate: float = 0.0   # % where expected value found
    hint_avg_latency_ms: float = 0.0
    
    # Combined
    overall_success_rate: float = 0.0
    
    # By category
    by_category: dict = field(default_factory=dict)
    
    # Individual results
    query_results: list[QueryResult] = field(default_factory=list)


def index_corpus(corpus_dir: Path, store_dir: Path, verbose: bool = True) -> float:
    """Index the corpus using MetadataHub."""
    from scripts.ingest import ingest
    
    start = time.time()
    
    config = init_config(str(store_dir))
    
    if verbose:
        print(f"\nIndexing corpus: {corpus_dir}")
        print(f"Store: {store_dir}")
    
    # Ingest all files in corpus directory
    result = ingest(
        corpus_dir,
        config,
        client=None,  # Use heuristic mode
        skip_vectors=False,
        verbose=verbose,
    )
    
    elapsed = time.time() - start
    
    if verbose:
        print(f"\nIndexing complete: {result['processed']} files in {elapsed:.1f}s")
    
    return elapsed


def run_tier1_search(
    query: str,
    expected_source: str,
    vector_store_dir: Path,
    top_k: int = 5,
) -> Tier1Result:
    """Run Tier 1 vector search."""
    start = time.time()
    
    results = search(query, vector_store_dir, top_k=top_k)
    
    latency = (time.time() - start) * 1000
    
    retrieved = [r["filename"] for r in results]
    scores = [r["score"] for r in results]
    
    # Check if expected source is in results
    hit = expected_source in retrieved
    rank = 0
    if hit:
        rank = retrieved.index(expected_source) + 1
    
    return Tier1Result(
        query=query,
        expected_source=expected_source,
        retrieved_sources=retrieved,
        scores=scores,
        hit=hit,
        rank=rank,
        latency_ms=latency,
    )


def _collect_all_nodes(node: dict, nodes: list) -> None:
    """Recursively collect all nodes from a tree."""
    nodes.append(node)
    for child in node.get("children", []):
        _collect_all_nodes(child, nodes)


def _find_node_by_path(root: dict, expected_path: list[str]) -> Optional[dict]:
    """Find a node matching the expected path."""
    current = root
    
    for path_elem in expected_path:
        if ":" in path_elem:
            path_type, path_value = path_elem.split(":", 1)
        else:
            path_type = None
            path_value = path_elem
        
        found = False
        for child in current.get("children", []):
            title = child.get("title", "").lower()
            
            # Match based on path type
            if path_type == "sheet":
                if "sheet" in title and path_value.lower() in title:
                    current = child
                    found = True
                    break
            elif path_type in ("class", "method", "function"):
                if path_value.lower() in title:
                    current = child
                    found = True
                    break
            elif path_type == "section":
                if path_value.lower() in title:
                    current = child
                    found = True
                    break
            else:
                if path_value.lower() in title:
                    current = child
                    found = True
                    break
        
        if not found:
            break
    
    return current if current != root else None


def check_hint_quality(
    tree: dict,
    expected_path: list[str],
    expected_value: Optional[str] = None,
    expected_content: Optional[list[str]] = None,
    store_dir: Optional[Path] = None,
) -> HintResult:
    """Check if the tree provides good navigation hints.
    
    Verifies:
    1. The tree contains a node matching the expected target
    2. The content at that node contains the expected value
    """
    start = time.time()
    
    root = tree.get("root", tree)
    
    # Collect all nodes for hint building
    all_nodes = []
    _collect_all_nodes(root, all_nodes)
    
    # Build combined hint from all node summaries
    hints = []
    for node in all_nodes:
        if node.get("hint"):
            hints.append(node["hint"])
        elif node.get("summary") and node.get("title"):
            hints.append(f"{node['title']}: {node['summary']}")
    
    combined_hint = "; ".join(hints[:10]) if hints else None  # Limit to avoid huge hints
    
    # Extract expected targets from path
    expected_targets = []
    for path_elem in expected_path:
        if ":" in path_elem:
            target_type, target_value = path_elem.split(":", 1)
            expected_targets.append((target_type, target_value))
    
    # Check if tree contains nodes matching expected targets
    hint_contains_target = False
    hint_contains_context = False
    
    # Check first target (e.g., sheet/class/section)
    if expected_targets:
        first_type, first_value = expected_targets[0]
        for node in all_nodes:
            title = node.get("title", "").lower()
            if first_value.lower() in title:
                hint_contains_target = True
                break
    
    # Check any path element matches (context)
    for _, target_value in expected_targets:
        for node in all_nodes:
            title = node.get("title", "").lower()
            summary = node.get("summary", "").lower()
            if target_value.lower() in title or target_value.lower() in summary:
                hint_contains_context = True
                break
        if hint_contains_context:
            break
    
    # Try to find the target node and read its content
    target_node = _find_node_by_path(root, expected_path)
    actual_content = ""
    content_preview = None
    
    if target_node:
        content_preview = target_node.get("preview") or target_node.get("summary")
        content_ref = target_node.get("content_ref")
        if content_ref and store_dir:
            content_path = store_dir / content_ref
            try:
                if content_path.exists():
                    actual_content = content_path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                pass
    
    # If no specific match, try to read all content from matching first-level target
    if not actual_content and expected_targets:
        first_type, first_value = expected_targets[0]
        for node in all_nodes:
            title = node.get("title", "").lower()
            if first_value.lower() in title:
                content_ref = node.get("content_ref")
                if content_ref and store_dir:
                    content_path = store_dir / content_ref
                    try:
                        if content_path.exists():
                            actual_content = content_path.read_text(encoding="utf-8", errors="ignore")
                            break
                    except Exception:
                        pass
    
    # Check if expected value is in content
    search_text = (content_preview or "") + " " + actual_content
    content_has_value = False
    if expected_value:
        content_has_value = expected_value.lower() in search_text.lower()
    elif expected_content:
        content_has_value = all(
            ec.lower() in search_text.lower() for ec in expected_content
        )
    else:
        content_has_value = True  # No expected content to match
    
    latency = (time.time() - start) * 1000
    
    return HintResult(
        expected_path=expected_path,
        hint=combined_hint[:500] if combined_hint else None,
        hint_contains_sheet=hint_contains_target,
        hint_contains_context=hint_contains_context,
        content_preview=content_preview[:200] if content_preview else None,
        content_has_value=content_has_value,
        latency_ms=latency,
    )


def run_benchmark(
    corpus_dir: Path,
    store_dir: Path,
    ground_truth_path: Path,
    skip_ingest: bool = False,
    verbose: bool = True,
) -> BenchmarkResults:
    """Run the simplified drill-down benchmark."""
    
    # Load ground truth
    with open(ground_truth_path) as f:
        ground_truth = json.load(f)
    
    queries = ground_truth["queries"]
    
    if verbose:
        print(f"\n{'='*60}")
        print("MetadataHub Drill-Down Benchmark (Simplified)")
        print(f"{'='*60}")
        print(f"Queries: {len(queries)}")
        print(f"Categories: {list(ground_truth['categories'].keys())}")
    
    # Index corpus
    index_time = 0.0
    if not skip_ingest:
        index_time = index_corpus(corpus_dir, store_dir, verbose=verbose)
    else:
        if verbose:
            print("\nSkipping indexing (using existing index)")
    
    # Load catalog and tree indexes
    config = Config(store_path=str(store_dir))
    catalog = load_catalog(config.catalog_path)
    
    if verbose:
        print(f"\nCatalog: {len(catalog['sources'])} sources")
        for src in catalog["sources"]:
            print(f"  - {src['filename']} ({src['type']}/{src['category']})")
    
    # Run queries
    results = BenchmarkResults(
        timestamp=datetime.now().isoformat(),
        corpus_path=str(corpus_dir),
        num_queries=len(queries),
        index_time_seconds=index_time,
    )
    
    tier1_hits = []
    tier1_ranks = []
    tier1_latencies = []
    hint_sheet_matches = []
    hint_context_matches = []
    content_matches = []
    hint_latencies = []
    successes = []
    
    by_category = {}
    
    if verbose:
        print(f"\n{'='*60}")
        print("Running Queries")
        print(f"{'='*60}")
    
    for query_data in queries:
        qid = query_data["id"]
        query = query_data["query"]
        category = query_data["category"]
        expected_source = query_data["tier1_expected_source"]
        expected_path = query_data["tier2_expected_path"]
        expected_value = query_data.get("expected_value")
        expected_content = query_data.get("expected_content_contains")
        
        if verbose:
            print(f"\n[{qid}] {query[:60]}...")
        
        # Tier 1: Source retrieval
        tier1 = run_tier1_search(
            query,
            expected_source,
            config.vector_store_path,
            top_k=5,
        )
        
        tier1_hits.append(1 if tier1.hit else 0)
        tier1_ranks.append(tier1.rank)
        tier1_latencies.append(tier1.latency_ms)
        
        if verbose:
            status = "✓" if tier1.hit else "✗"
            print(f"  Tier 1: {status} Source={tier1.retrieved_sources[0] if tier1.retrieved_sources else 'none'} (expected: {expected_source})")
        
        # Tier 2: Hint quality check
        hint_result = None
        if tier1.hit:
            # Find tree for the source
            source_entry = None
            for src in catalog["sources"]:
                if src["filename"] == expected_source:
                    source_entry = src
                    break
            
            if source_entry and source_entry.get("tree_path"):
                tree = load_tree(Path(source_entry["tree_path"]))
                if tree:
                    hint_result = check_hint_quality(
                        tree,
                        expected_path,
                        expected_value=expected_value,
                        expected_content=expected_content,
                        store_dir=store_dir,
                    )
                    
                    hint_sheet_matches.append(1 if hint_result.hint_contains_sheet else 0)
                    hint_context_matches.append(1 if hint_result.hint_contains_context else 0)
                    content_matches.append(1 if hint_result.content_has_value else 0)
                    hint_latencies.append(hint_result.latency_ms)
                    
                    if verbose:
                        sheet_status = "✓" if hint_result.hint_contains_sheet else "✗"
                        ctx_status = "✓" if hint_result.hint_contains_context else "✗"
                        val_status = "✓" if hint_result.content_has_value else "✗"
                        print(f"  Hint: Sheet={sheet_status} Context={ctx_status} Value={val_status}")
                        if hint_result.hint:
                            print(f"        Hint: {hint_result.hint[:80]}...")
        
        # Overall success: Tier 1 hit AND (hint includes sheet OR content has value)
        success = tier1.hit and hint_result is not None and (
            hint_result.hint_contains_sheet or hint_result.content_has_value
        )
        successes.append(1 if success else 0)
        
        # Record result
        qresult = QueryResult(
            id=qid,
            query=query,
            category=category,
            tier1=tier1,
            hint_result=hint_result,
            success=success,
        )
        results.query_results.append(qresult)
        
        # Track by category
        if category not in by_category:
            by_category[category] = {
                "count": 0,
                "tier1_hits": 0,
                "hint_sheet_matches": 0,
                "hint_context_matches": 0,
                "content_matches": 0,
                "successes": 0,
            }
        by_category[category]["count"] += 1
        by_category[category]["tier1_hits"] += 1 if tier1.hit else 0
        if hint_result:
            by_category[category]["hint_sheet_matches"] += 1 if hint_result.hint_contains_sheet else 0
            by_category[category]["hint_context_matches"] += 1 if hint_result.hint_contains_context else 0
            by_category[category]["content_matches"] += 1 if hint_result.content_has_value else 0
        by_category[category]["successes"] += 1 if success else 0
    
    # Calculate aggregate metrics
    n = len(queries)
    results.tier1_recall_at_1 = sum(1 for r in tier1_ranks if r == 1) / n
    results.tier1_recall_at_3 = sum(1 for r in tier1_ranks if 0 < r <= 3) / n
    results.tier1_recall_at_5 = sum(1 for r in tier1_ranks if 0 < r <= 5) / n
    results.tier1_mrr = sum(1/r for r in tier1_ranks if r > 0) / n
    results.tier1_avg_latency_ms = sum(tier1_latencies) / n if tier1_latencies else 0
    
    if hint_sheet_matches:
        results.hint_sheet_accuracy = sum(hint_sheet_matches) / len(hint_sheet_matches)
        results.hint_context_rate = sum(hint_context_matches) / len(hint_context_matches)
        results.content_match_rate = sum(content_matches) / len(content_matches)
        results.hint_avg_latency_ms = sum(hint_latencies) / len(hint_latencies)
    
    results.overall_success_rate = sum(successes) / n
    
    # Calculate category metrics
    for cat, data in by_category.items():
        cnt = data["count"]
        results.by_category[cat] = {
            "count": cnt,
            "tier1_recall": data["tier1_hits"] / cnt,
            "hint_sheet_accuracy": data["hint_sheet_matches"] / cnt,
            "hint_context_rate": data["hint_context_matches"] / cnt,
            "content_match_rate": data["content_matches"] / cnt,
            "success_rate": data["successes"] / cnt,
        }
    
    return results


def print_results(results: BenchmarkResults):
    """Print benchmark results in a nice format."""
    print(f"\n{'='*60}")
    print("BENCHMARK RESULTS")
    print(f"{'='*60}")
    
    print(f"\nTimestamp: {results.timestamp}")
    print(f"Corpus: {results.corpus_path}")
    print(f"Index Time: {results.index_time_seconds:.1f}s")
    print(f"Queries: {results.num_queries}")
    
    print(f"\n--- Tier 1: Source Retrieval ---")
    print(f"  Recall@1:  {results.tier1_recall_at_1:.1%}")
    print(f"  Recall@3:  {results.tier1_recall_at_3:.1%}")
    print(f"  Recall@5:  {results.tier1_recall_at_5:.1%}")
    print(f"  MRR:       {results.tier1_mrr:.3f}")
    print(f"  Avg Latency: {results.tier1_avg_latency_ms:.1f}ms")
    
    print(f"\n--- Tier 2: Hint Quality ---")
    print(f"  Sheet Accuracy:    {results.hint_sheet_accuracy:.1%}")
    print(f"  Context Rate:      {results.hint_context_rate:.1%}")
    print(f"  Content Match:     {results.content_match_rate:.1%}")
    print(f"  Avg Latency:       {results.hint_avg_latency_ms:.1f}ms")
    
    print(f"\n--- Overall ---")
    print(f"  Success Rate: {results.overall_success_rate:.1%}")
    
    print(f"\n--- By Category ---")
    for cat, metrics in results.by_category.items():
        print(f"\n  {cat} (n={metrics['count']}):")
        print(f"    Tier1 Recall:    {metrics['tier1_recall']:.1%}")
        print(f"    Sheet Accuracy:  {metrics['hint_sheet_accuracy']:.1%}")
        print(f"    Context Rate:    {metrics['hint_context_rate']:.1%}")
        print(f"    Content Match:   {metrics['content_match_rate']:.1%}")
        print(f"    Success Rate:    {metrics['success_rate']:.1%}")


def save_results(results: BenchmarkResults, output_path: Path):
    """Save results to JSON file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Create a serializable version
    output = {
        "timestamp": results.timestamp,
        "corpus_path": results.corpus_path,
        "num_queries": results.num_queries,
        "index_time_seconds": results.index_time_seconds,
        "tier1": {
            "recall_at_1": results.tier1_recall_at_1,
            "recall_at_3": results.tier1_recall_at_3,
            "recall_at_5": results.tier1_recall_at_5,
            "mrr": results.tier1_mrr,
            "avg_latency_ms": results.tier1_avg_latency_ms,
        },
        "tier2_hints": {
            "sheet_accuracy": results.hint_sheet_accuracy,
            "context_rate": results.hint_context_rate,
            "content_match_rate": results.content_match_rate,
            "avg_latency_ms": results.hint_avg_latency_ms,
        },
        "overall_success_rate": results.overall_success_rate,
        "by_category": results.by_category,
        "query_results": [asdict(qr) for qr in results.query_results],
    }
    
    with open(output_path, "w") as f:
        json.dump(output, f, indent=2, default=str)
    
    print(f"\nResults saved to: {output_path}")


def generate_markdown_report(results: BenchmarkResults, output_path: Path):
    """Generate a markdown report."""
    lines = [
        "# MetadataHub Drill-Down Benchmark Results",
        "",
        f"**Date:** {results.timestamp}",
        f"**Corpus:** {results.corpus_path}",
        f"**Queries:** {results.num_queries}",
        f"**Index Time:** {results.index_time_seconds:.1f}s",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Overall Success Rate | {results.overall_success_rate:.1%} |",
        f"| Tier 1 Recall@1 | {results.tier1_recall_at_1:.1%} |",
        f"| Tier 1 MRR | {results.tier1_mrr:.3f} |",
        f"| Hint Sheet Accuracy | {results.hint_sheet_accuracy:.1%} |",
        f"| Content Match | {results.content_match_rate:.1%} |",
        "",
        "## Tier 1: Source Retrieval",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Recall@1 | {results.tier1_recall_at_1:.1%} |",
        f"| Recall@3 | {results.tier1_recall_at_3:.1%} |",
        f"| Recall@5 | {results.tier1_recall_at_5:.1%} |",
        f"| MRR | {results.tier1_mrr:.3f} |",
        f"| Avg Latency | {results.tier1_avg_latency_ms:.1f}ms |",
        "",
        "## Tier 2: Hint Quality",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Sheet Accuracy | {results.hint_sheet_accuracy:.1%} |",
        f"| Context Rate | {results.hint_context_rate:.1%} |",
        f"| Content Match Rate | {results.content_match_rate:.1%} |",
        f"| Avg Latency | {results.hint_avg_latency_ms:.1f}ms |",
        "",
        "## Results by Category",
        "",
    ]
    
    for cat, metrics in results.by_category.items():
        lines.extend([
            f"### {cat}",
            "",
            f"- **Count:** {metrics['count']}",
            f"- **Tier 1 Recall:** {metrics['tier1_recall']:.1%}",
            f"- **Sheet Accuracy:** {metrics['hint_sheet_accuracy']:.1%}",
            f"- **Context Rate:** {metrics['hint_context_rate']:.1%}",
            f"- **Content Match:** {metrics['content_match_rate']:.1%}",
            f"- **Success Rate:** {metrics['success_rate']:.1%}",
            "",
        ])
    
    lines.extend([
        "## Individual Query Results",
        "",
        "| ID | Query | Category | Tier1 | Sheet | Context | Value | Success |",
        "|-----|-------|----------|-------|-------|---------|-------|---------|",
    ])
    
    for qr in results.query_results:
        t1 = "✓" if qr.tier1.hit else "✗"
        sheet = "✓" if qr.hint_result and qr.hint_result.hint_contains_sheet else "✗"
        ctx = "✓" if qr.hint_result and qr.hint_result.hint_contains_context else "✗"
        val = "✓" if qr.hint_result and qr.hint_result.content_has_value else "✗"
        success = "✓" if qr.success else "✗"
        query_short = qr.query[:40] + "..." if len(qr.query) > 40 else qr.query
        lines.append(f"| {qr.id} | {query_short} | {qr.category} | {t1} | {sheet} | {ctx} | {val} | {success} |")
    
    output_path.write_text("\n".join(lines))
    print(f"Markdown report saved to: {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Run MetadataHub drill-down benchmark"
    )
    parser.add_argument(
        "--corpus",
        type=str,
        default=str(Path(__file__).parent / "corpus"),
        help="Path to corpus directory",
    )
    parser.add_argument(
        "--store",
        type=str,
        default=str(Path(__file__).parent / "store"),
        help="Path to MetadataHub store",
    )
    parser.add_argument(
        "--ground-truth",
        type=str,
        default=str(Path(__file__).parent / "ground_truth_drilldown.json"),
        help="Path to ground truth JSON",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=str(Path(__file__).parent / "results"),
        help="Output directory for results",
    )
    parser.add_argument(
        "--skip-ingest",
        action="store_true",
        help="Skip corpus ingestion (use existing index)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Verbose output",
    )
    
    args = parser.parse_args()
    
    corpus_dir = Path(args.corpus)
    store_dir = Path(args.store)
    ground_truth_path = Path(args.ground_truth)
    output_dir = Path(args.output)
    
    # Run benchmark
    results = run_benchmark(
        corpus_dir=corpus_dir,
        store_dir=store_dir,
        ground_truth_path=ground_truth_path,
        skip_ingest=args.skip_ingest,
        verbose=args.verbose,
    )
    
    # Print results
    print_results(results)
    
    # Save results
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    save_results(results, output_dir / f"drilldown_{timestamp}.json")
    generate_markdown_report(results, output_dir / f"drilldown_{timestamp}.md")


if __name__ == "__main__":
    main()
