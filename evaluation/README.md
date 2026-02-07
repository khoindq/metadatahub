# MetadataHub Evaluation Framework

This directory contains the evaluation framework for measuring MetadataHub's retrieval quality.

## Overview

The evaluation framework measures:
- **Recall@K**: How many relevant documents are in the top K results
- **MRR (Mean Reciprocal Rank)**: Average position of first relevant result
- **Tree Accuracy**: How well tree navigation finds the correct nodes

## Files

```
evaluation/
├── README.md           # This file
├── ground_truth.json   # Sample queries with expected results
└── results/            # Evaluation run outputs (gitignored)
```

## Ground Truth Format

Each query in `ground_truth.json` has:

```json
{
  "id": "q1",
  "query": "What is the Q3 revenue?",
  "query_vi": "Doanh thu Q3 là bao nhiêu?",
  "category": "financial",
  "expected_sources": ["report_q3_2024.xlsx"],
  "expected_nodes": ["n_revenue"],
  "tags": ["revenue", "excel"]
}
```

- `query` / `query_vi`: Query in English and Vietnamese
- `category`: financial | code | documentation
- `expected_sources`: Files that should be retrieved
- `expected_nodes`: Tree nodes that contain the answer
- `tags`: Keywords for filtering

## Running Evaluation

### Basic Usage

```bash
# Run evaluation on all queries
python scripts/evaluate.py --store ~/.metadatahub/store

# Evaluate specific category
python scripts/evaluate.py --store ~/.metadatahub/store --category financial

# Use Vietnamese queries
python scripts/evaluate.py --store ~/.metadatahub/store --lang vi

# Custom K for Recall@K
python scripts/evaluate.py --store ~/.metadatahub/store --k 5

# Save results to file
python scripts/evaluate.py --store ~/.metadatahub/store --output evaluation/results/run_001.json
```

### Output

```
MetadataHub Evaluation Results
==============================
Store: ~/.metadatahub/store
Queries: 15
Language: en

Results:
  Recall@3: 0.73 (11/15 queries with relevant in top 3)
  Recall@5: 0.87 (13/15 queries with relevant in top 5)
  MRR: 0.65
  Tree Accuracy: 0.60

By Category:
  financial:     Recall@3=0.80, MRR=0.70
  code:          Recall@3=0.75, MRR=0.62
  documentation: Recall@3=0.67, MRR=0.58
```

## Comparing Runs

Use `compare_runs.py` to track improvements:

```bash
# Compare two runs
python scripts/compare_runs.py results/baseline.json results/improved.json

# Compare multiple runs
python scripts/compare_runs.py results/run_*.json --sort-by recall@3
```

Output:
```
Comparison: baseline.json vs improved.json
==========================================
Metric        Baseline    Improved    Delta
Recall@3      0.73        0.80        +0.07 ✓
Recall@5      0.87        0.93        +0.06 ✓
MRR           0.65        0.72        +0.07 ✓
Tree Acc      0.60        0.65        +0.05 ✓

Improvements: 4/4 metrics
```

## Adding Ground Truth

To add new test queries:

1. Edit `ground_truth.json`
2. Add a new query object with all required fields
3. Run evaluation to verify

### Tips for Good Ground Truth

- Include diverse query types (lookup, analytical, navigational)
- Mix Vietnamese and English queries
- Cover all supported file types
- Include edge cases (ambiguous queries, no results expected)

## Metrics Explained

### Recall@K

Measures: "Are relevant documents in the top K?"

```
Recall@K = (# relevant docs in top K) / (# total relevant docs)
```

Higher is better. A Recall@3 of 0.73 means 73% of queries have at least one relevant doc in top 3.

### Mean Reciprocal Rank (MRR)

Measures: "How high is the first relevant result?"

```
MRR = average(1 / rank of first relevant result)
```

Higher is better. MRR of 1.0 means first result is always relevant. MRR of 0.5 means first relevant is typically at position 2.

### Tree Accuracy

Measures: "Can we navigate to the correct tree node?"

```
Tree Accuracy = (# correct node retrievals) / (# total node lookups)
```

Evaluates the deep_retrieve → read_source pipeline.

## CI Integration

Add to your CI pipeline:

```yaml
- name: Run Evaluation
  run: |
    python scripts/evaluate.py --store ./test_store --output eval_results.json
    python scripts/compare_runs.py baseline.json eval_results.json --fail-on-regression
```

The `--fail-on-regression` flag exits with code 1 if any metric drops by more than 5%.
