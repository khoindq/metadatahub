#!/usr/bin/env python3
"""
Compare multiple MetadataHub evaluation runs.

Shows improvements and regressions between runs.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Optional


def load_run(path: str) -> dict:
    """Load evaluation run from JSON file."""
    with open(path) as f:
        return json.load(f)


def compare_two_runs(
    baseline: dict,
    improved: dict,
    threshold: float = 0.05
) -> dict:
    """
    Compare two evaluation runs.
    
    Args:
        baseline: Baseline run data
        improved: Improved run data
        threshold: Minimum delta to count as improvement/regression
    
    Returns:
        Comparison dict with deltas and status
    """
    comparison = {
        "baseline_timestamp": baseline.get("timestamp"),
        "improved_timestamp": improved.get("timestamp"),
        "metrics": {},
        "improvements": 0,
        "regressions": 0,
        "unchanged": 0
    }
    
    # Compare Recall@K
    baseline_recall = baseline.get("avg_recall_at_k", {})
    improved_recall = improved.get("avg_recall_at_k", {})
    
    for k in set(list(baseline_recall.keys()) + list(improved_recall.keys())):
        k_str = str(k)
        base_val = baseline_recall.get(k, baseline_recall.get(k_str, 0))
        imp_val = improved_recall.get(k, improved_recall.get(k_str, 0))
        delta = imp_val - base_val
        
        status = "unchanged"
        if delta > threshold:
            status = "improved"
            comparison["improvements"] += 1
        elif delta < -threshold:
            status = "regressed"
            comparison["regressions"] += 1
        else:
            comparison["unchanged"] += 1
        
        comparison["metrics"][f"recall@{k}"] = {
            "baseline": base_val,
            "improved": imp_val,
            "delta": delta,
            "status": status
        }
    
    # Compare MRR
    base_mrr = baseline.get("avg_mrr", 0)
    imp_mrr = improved.get("avg_mrr", 0)
    delta_mrr = imp_mrr - base_mrr
    
    status = "unchanged"
    if delta_mrr > threshold:
        status = "improved"
        comparison["improvements"] += 1
    elif delta_mrr < -threshold:
        status = "regressed"
        comparison["regressions"] += 1
    else:
        comparison["unchanged"] += 1
    
    comparison["metrics"]["mrr"] = {
        "baseline": base_mrr,
        "improved": imp_mrr,
        "delta": delta_mrr,
        "status": status
    }
    
    # Compare Tree Accuracy
    base_tree = baseline.get("avg_tree_accuracy", 0)
    imp_tree = improved.get("avg_tree_accuracy", 0)
    delta_tree = imp_tree - base_tree
    
    status = "unchanged"
    if delta_tree > threshold:
        status = "improved"
        comparison["improvements"] += 1
    elif delta_tree < -threshold:
        status = "regressed"
        comparison["regressions"] += 1
    else:
        comparison["unchanged"] += 1
    
    comparison["metrics"]["tree_accuracy"] = {
        "baseline": base_tree,
        "improved": imp_tree,
        "delta": delta_tree,
        "status": status
    }
    
    return comparison


def compare_multiple_runs(runs: list[tuple[str, dict]], sort_by: str = "recall@3") -> list[dict]:
    """
    Compare multiple runs and rank them.
    
    Args:
        runs: List of (name, run_data) tuples
        sort_by: Metric to sort by
    
    Returns:
        List of run summaries, sorted by specified metric
    """
    summaries = []
    
    for name, run in runs:
        summary = {
            "name": name,
            "timestamp": run.get("timestamp"),
            "num_queries": run.get("num_queries"),
            "metrics": {}
        }
        
        # Extract metrics
        recall = run.get("avg_recall_at_k", {})
        for k, v in recall.items():
            summary["metrics"][f"recall@{k}"] = v
        
        summary["metrics"]["mrr"] = run.get("avg_mrr", 0)
        summary["metrics"]["tree_accuracy"] = run.get("avg_tree_accuracy", 0)
        
        summaries.append(summary)
    
    # Sort by specified metric
    sort_key = sort_by.lower().replace("@", "@")
    summaries.sort(
        key=lambda x: x["metrics"].get(sort_key, x["metrics"].get(sort_by, 0)),
        reverse=True
    )
    
    return summaries


def print_comparison(comparison: dict, baseline_name: str, improved_name: str):
    """Print formatted comparison."""
    print(f"\nComparison: {baseline_name} vs {improved_name}")
    print("=" * 50)
    
    print(f"{'Metric':<15} {'Baseline':>10} {'Improved':>10} {'Delta':>10}")
    print("-" * 50)
    
    for metric, data in comparison["metrics"].items():
        delta_str = f"{data['delta']:+.2f}"
        status_icon = ""
        if data["status"] == "improved":
            status_icon = " ✓"
        elif data["status"] == "regressed":
            status_icon = " ✗"
        
        print(f"{metric:<15} {data['baseline']:>10.2f} {data['improved']:>10.2f} {delta_str:>10}{status_icon}")
    
    print("-" * 50)
    total = comparison["improvements"] + comparison["regressions"] + comparison["unchanged"]
    print(f"Improvements: {comparison['improvements']}/{total} metrics")
    
    if comparison["regressions"] > 0:
        print(f"⚠️  Regressions: {comparison['regressions']}/{total} metrics")


def print_ranking(summaries: list[dict], sort_by: str):
    """Print ranked comparison of multiple runs."""
    print(f"\nRanking by {sort_by}")
    print("=" * 70)
    
    # Header
    metrics = list(summaries[0]["metrics"].keys()) if summaries else []
    header = f"{'Rank':<5} {'Name':<20}"
    for m in metrics[:4]:  # Limit columns
        header += f" {m:>10}"
    print(header)
    print("-" * 70)
    
    for i, summary in enumerate(summaries, 1):
        row = f"{i:<5} {summary['name'][:20]:<20}"
        for m in metrics[:4]:
            row += f" {summary['metrics'].get(m, 0):>10.2f}"
        print(row)


def main():
    parser = argparse.ArgumentParser(
        description="Compare MetadataHub evaluation runs"
    )
    parser.add_argument(
        "runs",
        nargs="+",
        help="Evaluation run JSON files to compare"
    )
    parser.add_argument(
        "--sort-by",
        default="recall@3",
        help="Metric to sort by when comparing multiple runs (default: recall@3)"
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.05,
        help="Minimum delta to count as improvement/regression (default: 0.05)"
    )
    parser.add_argument(
        "--fail-on-regression",
        action="store_true",
        help="Exit with code 1 if any regression is detected (for CI)"
    )
    parser.add_argument(
        "--output", "-o",
        help="Save comparison to JSON file"
    )
    
    args = parser.parse_args()
    
    # Load all runs
    runs = []
    for path in args.runs:
        p = Path(path)
        if not p.exists():
            print(f"Error: File not found: {path}")
            sys.exit(1)
        runs.append((p.name, load_run(path)))
    
    if len(runs) == 0:
        print("Error: No runs to compare")
        sys.exit(1)
    
    if len(runs) == 1:
        # Single run - just show summary
        name, run = runs[0]
        print(f"\nSingle Run Summary: {name}")
        print("=" * 40)
        print(f"Queries: {run.get('num_queries')}")
        print(f"Timestamp: {run.get('timestamp')}")
        print("\nMetrics:")
        for k, v in run.get("avg_recall_at_k", {}).items():
            print(f"  Recall@{k}: {v:.2f}")
        print(f"  MRR: {run.get('avg_mrr', 0):.2f}")
        print(f"  Tree Accuracy: {run.get('avg_tree_accuracy', 0):.2f}")
        sys.exit(0)
    
    if len(runs) == 2:
        # Two runs - detailed comparison
        baseline_name, baseline = runs[0]
        improved_name, improved = runs[1]
        
        comparison = compare_two_runs(baseline, improved, threshold=args.threshold)
        print_comparison(comparison, baseline_name, improved_name)
        
        if args.output:
            with open(args.output, "w") as f:
                json.dump(comparison, f, indent=2)
            print(f"\nComparison saved to: {args.output}")
        
        if args.fail_on_regression and comparison["regressions"] > 0:
            print("\n❌ Failing due to regressions")
            sys.exit(1)
    
    else:
        # Multiple runs - ranking
        summaries = compare_multiple_runs(runs, sort_by=args.sort_by)
        print_ranking(summaries, args.sort_by)
        
        if args.output:
            with open(args.output, "w") as f:
                json.dump(summaries, f, indent=2)
            print(f"\nRanking saved to: {args.output}")
        
        # For CI: compare best vs worst
        if args.fail_on_regression and len(summaries) >= 2:
            # Assume first file is baseline, check if any later run is worse
            baseline = summaries[-1]  # Worst performer
            best = summaries[0]  # Best performer
            
            sort_metric = args.sort_by.lower()
            if best["metrics"].get(sort_metric, 0) < baseline["metrics"].get(sort_metric, 0) - args.threshold:
                print(f"\n❌ Best run ({best['name']}) is worse than baseline")
                sys.exit(1)


if __name__ == "__main__":
    main()
