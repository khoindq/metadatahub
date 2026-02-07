#!/usr/bin/env python3
"""
Benchmark Results Analyzer

Generates detailed analysis, charts, and comparison reports from benchmark results.

Usage:
    python analyze_results.py results.json
    python analyze_results.py results.json --format html
    python analyze_results.py results.json --compare baseline.json
"""

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any


def load_results(path: Path) -> dict:
    """Load benchmark results from JSON."""
    with open(path) as f:
        return json.load(f)


def calculate_winner(systems: list[dict], metric: str, higher_is_better: bool = True) -> str:
    """Determine which system wins for a metric."""
    if not systems:
        return "N/A"
    
    best_system = None
    best_value = None
    
    for s in systems:
        value = s.get(metric, 0)
        if best_value is None:
            best_value = value
            best_system = s["system_name"]
        elif higher_is_better and value > best_value:
            best_value = value
            best_system = s["system_name"]
        elif not higher_is_better and value < best_value:
            best_value = value
            best_system = s["system_name"]
    
    return best_system


def generate_summary(results: dict) -> str:
    """Generate a text summary of the results."""
    systems = results.get("systems", [])
    
    lines = [
        "=" * 70,
        "BENCHMARK ANALYSIS SUMMARY",
        "=" * 70,
        "",
        f"Timestamp: {results.get('timestamp', 'N/A')}",
        f"Corpus: {results.get('corpus_path', 'N/A')}",
        f"Total Queries: {results.get('num_queries', 0)}",
        "",
        "-" * 70,
        "OVERALL WINNERS BY METRIC",
        "-" * 70,
    ]
    
    metrics = [
        ("Best Recall@1", "recall_at_1", True),
        ("Best Recall@5", "recall_at_5", True),
        ("Best MRR", "mrr", True),
        ("Fastest Avg Latency", "avg_latency_ms", False),
        ("Smallest Index", "index_size_mb", False),
        ("Fastest Indexing", "index_time_seconds", False),
    ]
    
    for label, metric, higher_better in metrics:
        winner = calculate_winner(systems, metric, higher_better)
        winner_value = next(
            (s.get(metric, 0) for s in systems if s["system_name"] == winner),
            0
        )
        
        if "latency" in metric or "time" in metric:
            fmt_value = f"{winner_value:.1f}ms" if "latency" in metric else f"{winner_value:.2f}s"
        elif "size" in metric:
            fmt_value = f"{winner_value:.2f}MB"
        elif "recall" in metric:
            fmt_value = f"{winner_value:.1%}"
        else:
            fmt_value = f"{winner_value:.3f}"
        
        lines.append(f"  {label}: {winner} ({fmt_value})")
    
    lines.extend([
        "",
        "-" * 70,
        "DETAILED SCORES",
        "-" * 70,
    ])
    
    # Table header
    header = "| Metric".ljust(25) + "|"
    for s in systems:
        header += f" {s['system_name'][:15]}".ljust(17) + "|"
    lines.append(header)
    lines.append("|" + "-" * 24 + "|" + (("-" * 16 + "|") * len(systems)))
    
    # Table rows
    detail_metrics = [
        ("Recall@1", "recall_at_1", lambda x: f"{x:.1%}"),
        ("Recall@3", "recall_at_3", lambda x: f"{x:.1%}"),
        ("Recall@5", "recall_at_5", lambda x: f"{x:.1%}"),
        ("Recall@10", "recall_at_10", lambda x: f"{x:.1%}"),
        ("MRR", "mrr", lambda x: f"{x:.3f}"),
        ("Avg Latency (ms)", "avg_latency_ms", lambda x: f"{x:.1f}"),
        ("P50 Latency (ms)", "p50_latency_ms", lambda x: f"{x:.1f}"),
        ("P95 Latency (ms)", "p95_latency_ms", lambda x: f"{x:.1f}"),
        ("Index Size (MB)", "index_size_mb", lambda x: f"{x:.2f}"),
        ("Index Time (s)", "index_time_seconds", lambda x: f"{x:.2f}"),
        ("Documents", "num_documents", lambda x: f"{x:,}"),
        ("Chunks", "num_chunks", lambda x: f"{x:,}"),
    ]
    
    for label, attr, fmt in detail_metrics:
        row = f"| {label}".ljust(25) + "|"
        for s in systems:
            val = s.get(attr, 0)
            row += f" {fmt(val)}".ljust(17) + "|"
        lines.append(row)
    
    # Category breakdown
    lines.extend([
        "",
        "-" * 70,
        "PERFORMANCE BY CATEGORY",
        "-" * 70,
    ])
    
    categories = set()
    for s in systems:
        categories.update(s.get("metrics_by_category", {}).keys())
    
    for category in sorted(categories):
        lines.append(f"\n{category.upper()}")
        
        cat_header = "| Metric".ljust(20) + "|"
        for s in systems:
            cat_header += f" {s['system_name'][:12]}".ljust(14) + "|"
        lines.append(cat_header)
        lines.append("|" + "-" * 19 + "|" + (("-" * 13 + "|") * len(systems)))
        
        for metric, key in [("Recall@3", "recall_at_3"), ("Recall@5", "recall_at_5"), ("MRR", "mrr")]:
            row = f"| {metric}".ljust(20) + "|"
            for s in systems:
                cat_metrics = s.get("metrics_by_category", {}).get(category, {})
                val = cat_metrics.get(key, 0)
                fmt_val = f"{val:.1%}" if "recall" in key else f"{val:.3f}"
                row += f" {fmt_val}".ljust(14) + "|"
            lines.append(row)
    
    # Query-level analysis
    lines.extend([
        "",
        "-" * 70,
        "QUERY-LEVEL INSIGHTS",
        "-" * 70,
    ])
    
    for s in systems:
        query_results = s.get("query_results", [])
        if not query_results:
            continue
        
        # Find hardest queries (lowest MRR across all systems)
        failed_queries = [q for q in query_results if q.get("reciprocal_rank", 0) == 0]
        slow_queries = sorted(query_results, key=lambda q: q.get("latency_ms", 0), reverse=True)[:3]
        
        lines.append(f"\n{s['system_name']}:")
        lines.append(f"  - Queries with no hits: {len(failed_queries)}")
        
        if failed_queries[:3]:
            lines.append(f"  - Sample failed queries:")
            for q in failed_queries[:3]:
                lines.append(f"      • [{q.get('query_id')}] {q.get('query', '')[:50]}...")
        
        if slow_queries:
            lines.append(f"  - Slowest queries:")
            for q in slow_queries:
                lines.append(f"      • [{q.get('query_id')}] {q.get('latency_ms', 0):.1f}ms")
    
    lines.extend([
        "",
        "=" * 70,
        "END OF ANALYSIS",
        "=" * 70,
    ])
    
    return "\n".join(lines)


def generate_html_report(results: dict) -> str:
    """Generate an HTML report with charts."""
    systems = results.get("systems", [])
    
    # Prepare data for charts
    system_names = [s["system_name"] for s in systems]
    recall_data = {
        "Recall@1": [s.get("recall_at_1", 0) * 100 for s in systems],
        "Recall@3": [s.get("recall_at_3", 0) * 100 for s in systems],
        "Recall@5": [s.get("recall_at_5", 0) * 100 for s in systems],
        "Recall@10": [s.get("recall_at_10", 0) * 100 for s in systems],
    }
    mrr_data = [s.get("mrr", 0) for s in systems]
    latency_data = [s.get("avg_latency_ms", 0) for s in systems]
    
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>RAG Benchmark Report</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
            background: #f5f5f5;
        }}
        h1, h2, h3 {{
            color: #333;
        }}
        .card {{
            background: white;
            border-radius: 8px;
            padding: 20px;
            margin: 20px 0;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        .chart-container {{
            position: relative;
            height: 300px;
            margin: 20px 0;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
        }}
        th, td {{
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #ddd;
        }}
        th {{
            background: #f8f8f8;
        }}
        .winner {{
            color: #22c55e;
            font-weight: bold;
        }}
        .metric-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
        }}
        .metric-box {{
            background: #f8f8f8;
            padding: 15px;
            border-radius: 6px;
            text-align: center;
        }}
        .metric-value {{
            font-size: 2em;
            font-weight: bold;
            color: #3b82f6;
        }}
        .metric-label {{
            color: #666;
            margin-top: 5px;
        }}
    </style>
</head>
<body>
    <h1>🔍 RAG System Benchmark Report</h1>
    
    <div class="card">
        <h2>Overview</h2>
        <p><strong>Date:</strong> {results.get('timestamp', 'N/A')}</p>
        <p><strong>Corpus:</strong> {results.get('corpus_path', 'N/A')}</p>
        <p><strong>Total Queries:</strong> {results.get('num_queries', 0)}</p>
    </div>
    
    <div class="card">
        <h2>Recall Comparison</h2>
        <div class="chart-container">
            <canvas id="recallChart"></canvas>
        </div>
    </div>
    
    <div class="card">
        <h2>MRR & Latency</h2>
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px;">
            <div class="chart-container">
                <canvas id="mrrChart"></canvas>
            </div>
            <div class="chart-container">
                <canvas id="latencyChart"></canvas>
            </div>
        </div>
    </div>
    
    <div class="card">
        <h2>Detailed Results</h2>
        <table>
            <thead>
                <tr>
                    <th>Metric</th>
                    {"".join(f'<th>{s["system_name"]}</th>' for s in systems)}
                </tr>
            </thead>
            <tbody>
                <tr>
                    <td>Recall@1</td>
                    {"".join(f'<td>{s.get("recall_at_1", 0):.1%}</td>' for s in systems)}
                </tr>
                <tr>
                    <td>Recall@3</td>
                    {"".join(f'<td>{s.get("recall_at_3", 0):.1%}</td>' for s in systems)}
                </tr>
                <tr>
                    <td>Recall@5</td>
                    {"".join(f'<td>{s.get("recall_at_5", 0):.1%}</td>' for s in systems)}
                </tr>
                <tr>
                    <td>Recall@10</td>
                    {"".join(f'<td>{s.get("recall_at_10", 0):.1%}</td>' for s in systems)}
                </tr>
                <tr>
                    <td>MRR</td>
                    {"".join(f'<td>{s.get("mrr", 0):.3f}</td>' for s in systems)}
                </tr>
                <tr>
                    <td>Avg Latency (ms)</td>
                    {"".join(f'<td>{s.get("avg_latency_ms", 0):.1f}</td>' for s in systems)}
                </tr>
                <tr>
                    <td>P95 Latency (ms)</td>
                    {"".join(f'<td>{s.get("p95_latency_ms", 0):.1f}</td>' for s in systems)}
                </tr>
                <tr>
                    <td>Index Size (MB)</td>
                    {"".join(f'<td>{s.get("index_size_mb", 0):.2f}</td>' for s in systems)}
                </tr>
                <tr>
                    <td>Index Time (s)</td>
                    {"".join(f'<td>{s.get("index_time_seconds", 0):.2f}</td>' for s in systems)}
                </tr>
            </tbody>
        </table>
    </div>
    
    <script>
        // Recall Chart
        new Chart(document.getElementById('recallChart'), {{
            type: 'bar',
            data: {{
                labels: {json.dumps(system_names)},
                datasets: [
                    {{
                        label: 'Recall@1',
                        data: {json.dumps(recall_data["Recall@1"])},
                        backgroundColor: 'rgba(59, 130, 246, 0.8)',
                    }},
                    {{
                        label: 'Recall@3',
                        data: {json.dumps(recall_data["Recall@3"])},
                        backgroundColor: 'rgba(34, 197, 94, 0.8)',
                    }},
                    {{
                        label: 'Recall@5',
                        data: {json.dumps(recall_data["Recall@5"])},
                        backgroundColor: 'rgba(249, 115, 22, 0.8)',
                    }},
                    {{
                        label: 'Recall@10',
                        data: {json.dumps(recall_data["Recall@10"])},
                        backgroundColor: 'rgba(168, 85, 247, 0.8)',
                    }}
                ]
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                scales: {{
                    y: {{
                        beginAtZero: true,
                        max: 100,
                        title: {{ display: true, text: 'Recall (%)' }}
                    }}
                }}
            }}
        }});
        
        // MRR Chart
        new Chart(document.getElementById('mrrChart'), {{
            type: 'bar',
            data: {{
                labels: {json.dumps(system_names)},
                datasets: [{{
                    label: 'MRR',
                    data: {json.dumps(mrr_data)},
                    backgroundColor: 'rgba(34, 197, 94, 0.8)',
                }}]
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                scales: {{
                    y: {{
                        beginAtZero: true,
                        max: 1,
                        title: {{ display: true, text: 'MRR' }}
                    }}
                }}
            }}
        }});
        
        // Latency Chart
        new Chart(document.getElementById('latencyChart'), {{
            type: 'bar',
            data: {{
                labels: {json.dumps(system_names)},
                datasets: [{{
                    label: 'Avg Latency (ms)',
                    data: {json.dumps(latency_data)},
                    backgroundColor: 'rgba(249, 115, 22, 0.8)',
                }}]
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                scales: {{
                    y: {{
                        beginAtZero: true,
                        title: {{ display: true, text: 'Latency (ms)' }}
                    }}
                }}
            }}
        }});
    </script>
</body>
</html>"""
    
    return html


def compare_results(baseline: dict, current: dict) -> str:
    """Compare two benchmark results."""
    lines = [
        "=" * 70,
        "BENCHMARK COMPARISON",
        "=" * 70,
        "",
        f"Baseline: {baseline.get('timestamp', 'N/A')}",
        f"Current:  {current.get('timestamp', 'N/A')}",
        "",
    ]
    
    baseline_systems = {s["system_name"]: s for s in baseline.get("systems", [])}
    current_systems = {s["system_name"]: s for s in current.get("systems", [])}
    
    common_systems = set(baseline_systems.keys()) & set(current_systems.keys())
    
    for system in sorted(common_systems):
        b = baseline_systems[system]
        c = current_systems[system]
        
        lines.append(f"\n{system}")
        lines.append("-" * 40)
        
        metrics = [
            ("Recall@5", "recall_at_5", True),
            ("MRR", "mrr", True),
            ("Avg Latency", "avg_latency_ms", False),
            ("Index Size", "index_size_mb", False),
        ]
        
        for label, key, higher_better in metrics:
            b_val = b.get(key, 0)
            c_val = c.get(key, 0)
            delta = c_val - b_val
            
            if key in ["recall_at_5"]:
                fmt = lambda x: f"{x:.1%}"
            elif key in ["mrr"]:
                fmt = lambda x: f"{x:.3f}"
            else:
                fmt = lambda x: f"{x:.2f}"
            
            improved = (delta > 0 and higher_better) or (delta < 0 and not higher_better)
            symbol = "✓" if improved else "✗" if delta != 0 else "-"
            
            lines.append(f"  {label}: {fmt(b_val)} → {fmt(c_val)} ({'+' if delta > 0 else ''}{fmt(delta)}) {symbol}")
    
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Analyze benchmark results")
    parser.add_argument("results", type=Path, help="Benchmark results JSON file")
    parser.add_argument("--format", choices=["text", "html", "json"], default="text")
    parser.add_argument("--compare", type=Path, help="Baseline results to compare against")
    parser.add_argument("--output", type=Path, help="Output file")
    
    args = parser.parse_args()
    
    if not args.results.exists():
        print(f"Error: Results file not found: {args.results}")
        sys.exit(1)
    
    results = load_results(args.results)
    
    if args.compare:
        if not args.compare.exists():
            print(f"Error: Baseline file not found: {args.compare}")
            sys.exit(1)
        baseline = load_results(args.compare)
        output = compare_results(baseline, results)
    elif args.format == "text":
        output = generate_summary(results)
    elif args.format == "html":
        output = generate_html_report(results)
    elif args.format == "json":
        output = json.dumps(results, indent=2)
    else:
        output = generate_summary(results)
    
    if args.output:
        with open(args.output, "w") as f:
            f.write(output)
        print(f"Output saved to {args.output}")
    else:
        print(output)


if __name__ == "__main__":
    main()
